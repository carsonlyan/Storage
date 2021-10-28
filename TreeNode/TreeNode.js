import React, { useCallback, useEffect, useState } from 'react';
import TreeView from '@mui/lab/TreeView';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import TreeItem from '@mui/lab/TreeItem';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';

const checkMap = {
  2: 'checked',
  1: 'partChecked',
  0: ''
}

const TreeNode = ({ label, id, checked, onCheck }) => {
  return (
    <FormGroup>
      <FormControlLabel control={<Checkbox id={id} checked={checked===2? true:false} indeterminate={checked===1? true:false} onChange={(e) => onCheck(e)} />} label={label} />
    </FormGroup>
  )
}

export function TreeNodeComp({ data, checkedNodeIDs, onCheck }) {
  const [treeData, setTreeData] = useState(data);

  const updateChildrenNodes = useCallback(
    (node, isChecked) => {
      node.children.forEach((childNode) => {
        childNode.checked = isChecked;
        updateChildrenNodes(childNode, isChecked);
      })
    }, []);
  
  const updateCheckedNodes = useCallback(
    (tree_data, id, isChecked, deepth) => {
      const parentId = id.slice(0, -1);
      function findParentNode (node) {
        for(const childNode of node) {
          if(childNode.id === parentId) return childNode;
          else {
            const res = findParentNode(childNode.children);
            if(res) return res;
          }
        }
      }
      if(!parentId) {
        const node = tree_data.find((node) => node.id === id);
        node.checked = isChecked;
        if(deepth === 0) updateChildrenNodes(node, isChecked);
        return;
      } 
      const parentNode = findParentNode(tree_data);
      const childrenNodes = parentNode.children;
      if(deepth === 0) {
        const node = childrenNodes.find((node) => node.id === id);
        updateChildrenNodes(node, isChecked);
      }
      if(isChecked) {
        let allChildrenChecked = true;
        childrenNodes.forEach((node) => {
          if (node.id === id) node.checked = isChecked;
          else if(node.checked !== 2) allChildrenChecked = false;
        })
        if (allChildrenChecked) parentNode.checked = 2;
        else parentNode.checked = 1;
      } else {
        let allChildrenNotChecked = true;
        childrenNodes.forEach((node) => {
          if(node.id === id) node.checked = isChecked;
          else if(node.checked !== 0) allChildrenNotChecked = false;
        })
        if (allChildrenNotChecked) parentNode.checked = 0;
        else parentNode.checked = 1;
      }
      updateCheckedNodes(tree_data, parentId, parentNode.checked, ++deepth);
    }, [updateChildrenNodes])

  useEffect(() => {
    setTreeData((prevTreeData) => {
      const tempTreeData = JSON.parse(JSON.stringify(prevTreeData));
      checkedNodeIDs.forEach((id) => updateCheckedNodes(tempTreeData, id, 2, 0))
      return tempTreeData;
    })
  }, [checkedNodeIDs, updateCheckedNodes])

  const collectCheckedNodes = (nodes, checkedNodes) => {
    nodes.forEach((node) => {
      if (node.checked === 2) {
        checkedNodes.push(node);
        collectCheckedNodes(node.children, checkedNodes);
      }
      else collectCheckedNodes(node.children, checkedNodes);
    })
  }

  const handleOnCheck = (event) => {
    const id = event.target.id;
    const isChecked = event.target.checked;
    setTreeData((prevTreeData) => {
      const tempTreeData = JSON.parse(JSON.stringify(prevTreeData));
      updateCheckedNodes(tempTreeData, id, isChecked?2:0, 0);
      const checkedNodes = [];
      collectCheckedNodes(tempTreeData, checkedNodes);
      onCheck(checkedNodes);
      return tempTreeData;
    })

  }

  const renderNode = (node) => {
    const { id, checked, name } = node;

    return (
      <TreeItem key={id} nodeId={id} label={<TreeNode label={name} id={id} checked={checked} onCheck={handleOnCheck} />}>
        {node.children.map((childNode) => {
          return renderNode(childNode);
        })}
      </TreeItem>
    )
  }

  return (
    <TreeView
      aria-label="multi-select"
      defaultCollapseIcon={<ExpandMoreIcon />}
      defaultExpandIcon={<ChevronRightIcon />}
      sx={{ width: '100%' }}
    >
      {treeData.map((node) => renderNode(node))}
    </TreeView>
  );
}